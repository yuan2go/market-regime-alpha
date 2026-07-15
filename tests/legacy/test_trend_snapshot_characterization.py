from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from market_regime_alpha.dividend_t import trend_snapshot
from market_regime_alpha.dividend_t.models import (
    RetreatInputs,
    ScoreBreakdown,
    Signal,
    StrategyDecision,
    TechnicalInputs,
    WatchlistItem,
)


class _FixtureProvider:
    data_source = "fixture-5min"

    def minute_bars(
        self,
        symbol: str,
        *,
        freq: str = "5min",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        del symbol, freq, start_date, end_date
        frame = pd.DataFrame(
            {
                "timestamp": ["2026-07-15 14:50:00", "2026-07-15 14:55:00"],
                "open": [10.0, 10.1],
                "high": [10.2, 10.3],
                "low": [9.9, 10.0],
                "close": [10.1, 10.2],
                "volume": [1000.0, 1200.0],
                "amount": [10100.0, 12240.0],
            }
        )
        frame.attrs["data_source"] = self.data_source
        return frame


class _FixtureStrategy:
    def evaluate(self, **_: object) -> StrategyDecision:
        return StrategyDecision(
            symbol="000001.SZ",
            signal=Signal.HOLD,
            score=ScoreBreakdown(
                F_score=75.0,
                G_score=3.0,
                Z_score=3.0,
                K_score=3.0,
                S_score=2.0,
                R_score=70.0,
                T_score=72.0,
                total_score=72.5,
                C_score=65.0,
            ),
            base_position_limit_pct=0.10,
            suggested_trade_pct=0.0,
            reasons=("Legacy strategy says hold.",),
        )


def test_legacy_snapshot_row_exposes_strategy_signal_and_timing_action_independently(monkeypatch) -> None:
    technical = TechnicalInputs(
        position_quality=70.0,
        volume_structure=70.0,
        trend_quality=70.0,
        intraday_support=70.0,
    )
    monkeypatch.setattr(trend_snapshot, "infer_technical_inputs", lambda bars: technical)
    monkeypatch.setattr(
        trend_snapshot,
        "infer_retreat_inputs",
        lambda bars, current: RetreatInputs(3.0, 3.0, 2.0, 2.0),
    )
    monkeypatch.setattr(
        trend_snapshot,
        "estimate_levels",
        lambda bars, support_window, resistance_window: SimpleNamespace(support=9.8, resistance=10.8),
    )
    monkeypatch.setattr(
        trend_snapshot,
        "_timing_payload",
        lambda **_: {
            "timing_status": "ok",
            "timing_action": "BUY_T_TIMING",
            "timing_action_label": "买点",
            "timing_point_type": "buy",
            "timing_point_label": "买点",
        },
    )

    row = trend_snapshot._build_symbol_row(
        item=WatchlistItem(
            symbol="000001.SZ",
            name="Fixture",
            industry="Bank",
            is_cycle_stock=False,
        ),
        provider=_FixtureProvider(),
        quote=None,
        strategy=_FixtureStrategy(),  # type: ignore[arg-type]
        min_bars=2,
    )

    assert row["status"] == "ok"
    assert row["signal"] == "HOLD"
    assert row["timing_action"] == "BUY_T_TIMING"
    assert row["signal"] != row["timing_action"]
    assert row["confidence"] == 71
    assert row["reasons"] == ["Legacy strategy says hold."]


def test_legacy_snapshot_timing_error_does_not_replace_strategy_signal(monkeypatch) -> None:
    technical = TechnicalInputs(
        position_quality=70.0,
        volume_structure=70.0,
        trend_quality=70.0,
        intraday_support=70.0,
    )
    monkeypatch.setattr(trend_snapshot, "infer_technical_inputs", lambda bars: technical)
    monkeypatch.setattr(
        trend_snapshot,
        "infer_retreat_inputs",
        lambda bars, current: RetreatInputs(3.0, 3.0, 2.0, 2.0),
    )
    monkeypatch.setattr(
        trend_snapshot,
        "estimate_levels",
        lambda bars, support_window, resistance_window: SimpleNamespace(support=9.8, resistance=10.8),
    )
    monkeypatch.setattr(
        trend_snapshot,
        "_timing_payload",
        lambda **_: {
            "timing_status": "error",
            "timing_action": "ERROR",
            "timing_action_label": "计算失败",
            "timing_point_type": "none",
            "timing_point_label": "无信号",
        },
    )

    row = trend_snapshot._build_symbol_row(
        item=WatchlistItem(
            symbol="000001.SZ",
            name="Fixture",
            industry="Bank",
            is_cycle_stock=False,
        ),
        provider=_FixtureProvider(),
        quote=None,
        strategy=_FixtureStrategy(),  # type: ignore[arg-type]
        min_bars=2,
    )

    assert row["signal"] == "HOLD"
    assert row["timing_status"] == "error"
    assert row["timing_action"] == "ERROR"
