from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from market_regime_alpha.research.mr2a_regime import (
    FEATURE_DIRECTIONS,
    build_decision_time_context,
    controlled_heterogeneity_gate,
    spearman_rank_ic,
)
from market_regime_alpha.research.tencent_composite_contracts import CompositeBar, CompositeSourceKind, PreparedCompositeData, PreparedCompositeSession


TZ = ZoneInfo("Asia/Shanghai")


def _bar(day: date, hour: int, minute: int, close: float, amount: float) -> CompositeBar:
    return CompositeBar("A", datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ), close, close + 1, close - 1, close, 1.0, amount, CompositeSourceKind.LOCAL)


def _prepared() -> PreparedCompositeData:
    days = (date(2026, 1, 5), date(2026, 1, 6))
    sessions = tuple(PreparedCompositeSession("A", day, 10, 11, 9, 10, 1, 10, datetime(day.year, day.month, day.day, 14, 50, tzinfo=TZ), (CompositeSourceKind.LOCAL,)) for day in days)
    return PreparedCompositeData(("A",), days, sessions, type("Q", (), {"accepted_symbols": ("A",)})(), ())


def test_context_ignores_decision_date_after_cutoff_bars() -> None:
    prepared = _prepared()
    before = (_bar(date(2026, 1, 5), 14, 50, 10, 10), _bar(date(2026, 1, 6), 14, 50, 10, 10))
    after = before + (_bar(date(2026, 1, 6), 15, 0, 100, 1_000_000),)
    first = build_decision_time_context(prepared=prepared, bars=before, decision_dates=(date(2026, 1, 6),))
    second = build_decision_time_context(prepared=prepared, bars=after, decision_dates=(date(2026, 1, 6),))
    assert first == second


def test_true_spearman_and_direction_registry() -> None:
    assert spearman_rank_ic([1, 2, 3], [1, 4, 9]) == 1.0
    assert FEATURE_DIRECTIONS["feature-r5-volatility-20s-v1"] == "LOWER_IS_BETTER"
    assert FEATURE_DIRECTIONS["feature-r5-momentum-5s-v1"] == "HIGHER_IS_BETTER"


def test_weak_opposite_signs_do_not_promote_regime_hypothesis() -> None:
    result = controlled_heterogeneity_gate([0.0001] * 15, [-0.0001] * 15, seed=7)
    assert result["assessment"] == "C0. REGIME_HETEROGENEITY_NOT_SUPPORTED"
