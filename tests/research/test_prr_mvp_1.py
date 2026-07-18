from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.research.prr_mvp_1 import (
    ExploratoryExecutionCostConfig,
    PRRCandidateData,
    acceptance_accounting,
    replay_fixed_candidate_portfolios,
)
from market_regime_alpha.research.prr_mvp_1_artifacts import (
    FAILURE_FILENAMES,
    write_prr_failure,
)
from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeDispositionCode,
    CompositeQualityReport,
    CompositeSourceKind,
    CompositeSymbolDisposition,
    PreparedCompositeData,
    PreparedCompositeSession,
)


TZ = ZoneInfo("Asia/Shanghai")
SYMBOL = "000001.SZ"


def _execution() -> SimpleNamespace:
    dates = tuple(date(2026, 1, 1) + timedelta(days=index) for index in range(61))
    quality = CompositeQualityReport(
        requested_symbols=(SYMBOL,),
        accepted_symbols=(SYMBOL,),
        dispositions=(
            CompositeSymbolDisposition(SYMBOL, CompositeDispositionCode.ACCEPTED, 61, ()),
        ),
        common_session_dates=dates,
        required_session_count=61,
        minimum_accepted_symbols=1,
    )
    prepared = PreparedCompositeData(
        accepted_symbols=(SYMBOL,),
        common_session_dates=dates,
        sessions=tuple(
            PreparedCompositeSession(
                symbol=SYMBOL,
                session_date=value,
                open=10.0,
                high=10.3,
                low=9.9,
                close=10.2,
                amount=1_000_000.0,
                reference_price=10.0,
                reference_timestamp=datetime(value.year, value.month, value.day, 14, 50, tzinfo=TZ),
                source_kinds=(CompositeSourceKind.LOCAL,),
            )
            for value in dates
        ),
        quality=quality,
        limitations=("AUXILIARY_DATA_ONLY",),
    )
    return SimpleNamespace(prepared=prepared, dataset_contract=SimpleNamespace(dataset_id="dataset-test"))


def _candidate_data() -> PRRCandidateData:
    execution = _execution()
    decisions = execution.prepared.common_session_dates[:-1]
    rows = tuple(
        {
            "decision_date": value.isoformat(),
            "decision_time": datetime(value.year, value.month, value.day, 14, 55, tzinfo=TZ).isoformat(),
            "target_id": "target-r5-decision-reference-to-next-session-close-return-v1",
            "model_id": "prr-mvp-1-b0-test",
            "symbol": SYMBOL,
            "eligible_for_ranking": True,
            "rank": 1,
        }
        for value in decisions
    )
    return PRRCandidateData(decision_dates=decisions, datasets=(), ranking_rows=rows)


def test_cost_config_rejects_negative_assumptions() -> None:
    with pytest.raises(ValueError):
        ExploratoryExecutionCostConfig(entry_slippage_bps=-0.1)


def test_replay_is_chronological_cash_constrained_and_net_of_costs() -> None:
    result = replay_fixed_candidate_portfolios(
        execution=_execution(),
        candidate_data=_candidate_data(),
        run_id="run-test",
        top_k=5,
        cost_config=ExploratoryExecutionCostConfig(),
    )

    assert result.trades
    assert all(item["gross_return"] > item["net_return"] for item in result.trades)
    assert all(item["rank"] == 1 for item in result.trades)
    assert any(item["reason_code"] == "ACTIVE_POSITION_CASH_LOCKED" for item in result.orders)
    assert all(
        trade["exit_date"] > trade["entry_date"]
        for trade in result.trades
    )
    accounting = acceptance_accounting(
        replay=result,
        model_count=1,
        decision_date_count=60,
        top_k=5,
    )
    assert accounting["selection_slot_count"] == 300
    assert (
        accounting["completed_trade_count"]
        + accounting["cash_slot_count"]
        + accounting["excluded_count"]
        == 300
    )
    assert all(item["fill_status"] == "SIMULATED_REFERENCE_FILL" for item in result.fills)


def test_failure_artifact_is_non_overwriting_and_hashed(tmp_path: Path) -> None:
    path = write_prr_failure(
        root=tmp_path,
        run_id="failed-run",
        config_snapshot={"mode": "LIVE"},
        error=RuntimeError("network unavailable"),
    )

    assert {item.name for item in path.iterdir()} == FAILURE_FILENAMES
    with pytest.raises(FileExistsError):
        write_prr_failure(
            root=tmp_path,
            run_id="failed-run",
            config_snapshot={"mode": "LIVE"},
            error=RuntimeError("network unavailable"),
        )
