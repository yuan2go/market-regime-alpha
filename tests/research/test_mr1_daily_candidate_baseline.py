from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.research.mr1_candidate_baselines import (
    CandidateBaselineId,
    build_candidate_daily_baselines,
    build_model_candidate_populations,
    compound_candidate_baselines,
    daily_selection_lifts,
    select_matched_k_symbols,
)
from market_regime_alpha.research.mr1_morning_pop import MR1ExitTime, replay_mr1_fixed_portfolios
from market_regime_alpha.research.prr_mvp_1 import ExploratoryExecutionCostConfig
from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeSourceKind,
    PreparedCompositeData,
    PreparedCompositeSession,
)


SYMBOLS = tuple(f"{index:06d}.SZ" for index in range(1, 21))
TZ = ZoneInfo("Asia/Shanghai")


def _targets(days: tuple[date, ...], *, missing_symbol: str | None = None) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    target_ids = (
        "NEXT_SESSION_0935_RETURN",
        "NEXT_SESSION_1000_RETURN",
        "NEXT_SESSION_1030_RETURN",
        "NEXT_SESSION_CLOSE_RETURN",
    )
    for day in days:
        for target_id in target_ids:
            for symbol in SYMBOLS:
                available = symbol != missing_symbol
                rows.append(
                    {
                        "decision_date": day.isoformat(),
                        "target_session_date": (day + timedelta(days=1)).isoformat(),
                        "target_id": target_id,
                        "symbol": symbol,
                        "status": "AVAILABLE" if available else "UNAVAILABLE",
                        "value": 0.01 if available else None,
                        "reference_price": 10.0 if available else None,
                        "exit_price": 10.1 if available else None,
                        "exit_timestamp": datetime(
                            day.year,
                            day.month,
                            day.day,
                            10,
                            30,
                            tzinfo=TZ,
                        ).isoformat()
                        if available
                        else None,
                    }
                )
    return tuple(rows)


def _rows_by_id(rows: tuple[dict[str, object], ...]) -> dict[CandidateBaselineId, dict[str, object]]:
    return {
        CandidateBaselineId(str(row["baseline_id"])): row
        for row in rows
        if row["exit_time"] == "10:30" and row["cost_scenario"] == "BASE"
    }


def _populations(
    days: tuple[date, ...],
    symbols: tuple[str, ...] = SYMBOLS,
) -> tuple[object, ...]:
    return build_model_candidate_populations(
        dataset_id="prr-dataset-test",
        ranking_rows=tuple(
            {
                "decision_date": day.isoformat(),
                "target_id": "target-r5-decision-reference-to-next-session-close-return-v1",
                "model_id": "fixed-b0",
                "symbol": symbol,
                "eligible_for_ranking": True,
                "rank": rank,
            }
            for day in days
            for rank, symbol in enumerate(symbols, start=1)
        ),
    )


def test_missing_target_keeps_original_weight_as_cash() -> None:
    result = build_candidate_daily_baselines(
        populations=_populations((date(2026, 1, 5),)),
        target_rows=_targets((date(2026, 1, 5),), missing_symbol=SYMBOLS[-1]),
        decision_dates=(date(2026, 1, 5),),
        cost_configs={"BASE": ExploratoryExecutionCostConfig(minimum_commission=0.0)},
        top_k=5,
        baseline_seed=17,
    )
    by_id = _rows_by_id(result.baseline_rows)

    all_candidate = by_id[CandidateBaselineId.ALL_CANDIDATE_GROSS_V1]
    assert all_candidate["observed_weight"] == pytest.approx(0.95)
    assert all_candidate["missing_weight"] == pytest.approx(0.05)
    assert float(all_candidate["observed_weight"]) + float(all_candidate["missing_weight"]) == pytest.approx(1.0)


def test_minimum_commission_bias_is_separated_from_ranking_lift() -> None:
    day = date(2026, 1, 5)
    result = build_candidate_daily_baselines(
        populations=_populations((day,)),
        target_rows=_targets((day,)),
        decision_dates=(day,),
        cost_configs={"BASE": ExploratoryExecutionCostConfig(minimum_commission=50.0)},
        top_k=5,
        baseline_seed=17,
    )
    by_id = _rows_by_id(result.baseline_rows)
    matched_gross = by_id[CandidateBaselineId.MATCHED_K_HASH_GROSS_V1]
    matched_net = by_id[CandidateBaselineId.MATCHED_K_HASH_NET_V1]
    all_net = by_id[CandidateBaselineId.ALL_CANDIDATE_NET_DIAGNOSTIC_V1]

    assert matched_gross["gross_return"] == pytest.approx(all_net["gross_return"])
    assert matched_net["net_return"] > all_net["net_return"]
    lifts = daily_selection_lifts(
        model_gross_return=float(matched_gross["gross_return"]),
        model_net_return=float(matched_net["net_return"]),
        baseline_rows=result.baseline_rows,
    )
    assert lifts["gross_selection_lift_vs_matched_k"] == pytest.approx(0.0)
    assert lifts["net_selection_lift_vs_matched_k"] == pytest.approx(0.0)
    assert lifts["cost_drag_difference"] == pytest.approx(0.0)


def test_matched_k_selection_is_stable_and_rank_blind() -> None:
    selected = select_matched_k_symbols(
        dataset_id="prr-dataset-test",
        decision_date=date(2026, 1, 5),
        symbols=reversed(SYMBOLS),
        top_k=5,
        baseline_seed=17,
    )

    assert selected == select_matched_k_symbols(
        dataset_id="prr-dataset-test",
        decision_date=date(2026, 1, 5),
        symbols=SYMBOLS,
        top_k=5,
        baseline_seed=17,
    )
    assert len(selected) == 5


def test_matched_k_and_identical_model_selection_have_zero_gross_net_and_cost_difference() -> None:
    day = date(2026, 1, 5)
    target_rows = tuple(row for row in _targets((day,)) if row["symbol"] == SYMBOLS[0])
    costs = ExploratoryExecutionCostConfig(minimum_commission=50.0)
    baseline_result = build_candidate_daily_baselines(
        populations=_populations((day,), (SYMBOLS[0],)),
        target_rows=target_rows,
        decision_dates=(day,),
        cost_configs={"BASE": costs},
        top_k=1,
        baseline_seed=17,
    )
    replay = replay_mr1_fixed_portfolios(
        prepared=_prepared_one_symbol((day, day + timedelta(days=1))),
        ranking_rows=(
            {
                "decision_date": day.isoformat(),
                "target_id": "target-r5-decision-reference-to-next-session-close-return-v1",
                "model_id": "fixed-b0",
                "symbol": SYMBOLS[0],
                "eligible_for_ranking": True,
                "rank": 1,
            },
        ),
        target_rows=target_rows,
        decision_dates=(day,),
        top_k=1,
        exit_time=MR1ExitTime.T_1030,
        cost_scenario="BASE",
        cost_config=costs,
    )
    lifts = daily_selection_lifts(
        model_gross_return=float(replay.daily_equity[0]["gross_return"]),
        model_net_return=float(replay.daily_equity[0]["net_return"]),
        baseline_rows=(
            row
            for row in baseline_result.baseline_rows
            if row["exit_time"] == "10:30" and row["cost_scenario"] == "BASE"
        ),
    )

    assert lifts["gross_selection_lift_vs_matched_k"] == pytest.approx(0.0)
    assert lifts["net_selection_lift_vs_matched_k"] == pytest.approx(0.0)
    assert lifts["cost_drag_difference"] == pytest.approx(0.0)


def test_close_baselines_preserve_alternating_cash_lock() -> None:
    days = tuple(date(2026, 1, 5) + timedelta(days=index) for index in range(4))
    result = build_candidate_daily_baselines(
        populations=_populations(days),
        target_rows=_targets(days),
        decision_dates=days,
        cost_configs={"BASE": ExploratoryExecutionCostConfig()},
        top_k=5,
        baseline_seed=17,
    )
    matched = [
        row
        for row in result.baseline_rows
        if row["baseline_id"] == CandidateBaselineId.MATCHED_K_HASH_NET_V1.value
        and row["exit_time"] == "CLOSE"
    ]

    assert [row["baseline_slot_status"] for row in matched] == [
        "EXECUTED",
        "CASH_LOCKED",
        "EXECUTED",
        "CASH_LOCKED",
    ]
    assert [row["cash_locked_weight"] for row in matched] == [0.0, 1.0, 0.0, 1.0]

    model_targets = tuple(row for row in _targets(days) if row["symbol"] == SYMBOLS[0])
    replay = replay_mr1_fixed_portfolios(
        prepared=_prepared_one_symbol((*days, days[-1] + timedelta(days=1))),
        ranking_rows=tuple(
            {
                "decision_date": day.isoformat(),
                "target_id": "target-r5-decision-reference-to-next-session-close-return-v1",
                "model_id": "fixed-b0",
                "symbol": SYMBOLS[0],
                "eligible_for_ranking": True,
                "rank": 1,
            }
            for day in days
        ),
        target_rows=model_targets,
        decision_dates=days,
        top_k=1,
        exit_time=MR1ExitTime.CLOSE,
        cost_scenario="BASE",
    )
    model_locked_dates = [
        row["decision_date"]
        for row in replay.orders
        if row["reason_code"] == "ACTIVE_POSITION_CASH_LOCKED"
    ]
    baseline_locked_dates = [
        row["decision_date"] for row in matched if row["baseline_slot_status"] == "CASH_LOCKED"
    ]
    assert model_locked_dates == baseline_locked_dates


def test_compounding_uses_only_daily_baseline_rows() -> None:
    values = compound_candidate_baselines(
        (
            {
                "baseline_id": CandidateBaselineId.MATCHED_K_HASH_NET_V1.value,
                "model_id": "fixed-b0",
                "cost_scenario": "BASE",
                "exit_time": "10:30",
                "gross_return": 0.10,
                "net_return": 0.08,
            },
            {
                "baseline_id": CandidateBaselineId.MATCHED_K_HASH_NET_V1.value,
                "model_id": "fixed-b0",
                "cost_scenario": "BASE",
                "exit_time": "10:30",
                "gross_return": -0.10,
                "net_return": -0.08,
            },
        )
    )

    key = ("fixed-b0", CandidateBaselineId.MATCHED_K_HASH_NET_V1.value, "BASE", "10:30")
    assert values[key] == pytest.approx({"gross": -0.01, "net": -0.0064})


def _prepared_one_symbol(days: tuple[date, ...]) -> PreparedCompositeData:
    sessions = tuple(
        PreparedCompositeSession(
            symbol=SYMBOLS[0],
            session_date=day,
            open=10.0,
            high=10.2,
            low=9.8,
            close=10.1,
            amount=100.0,
            reference_price=10.0,
            reference_timestamp=datetime(day.year, day.month, day.day, 14, 50, tzinfo=TZ),
            source_kinds=(CompositeSourceKind.LOCAL,),
        )
        for day in days
    )
    return PreparedCompositeData(
        accepted_symbols=(SYMBOLS[0],),
        common_session_dates=days,
        sessions=sessions,
        quality=SimpleNamespace(accepted_symbols=(SYMBOLS[0],)),
        limitations=(),
    )
