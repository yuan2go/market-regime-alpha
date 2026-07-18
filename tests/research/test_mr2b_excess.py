from market_regime_alpha.research.mr2b_excess import primary_assessment


def test_absolute_market_moves_without_excess_cannot_support_primary() -> None:
    rows = [("2026-01-01", "UP", .02, .02), ("2026-01-02", "DOWN", -.02, -.02)] * 15
    assert primary_assessment(rows)["assessment"] == "NO_EXCESS_CONDITIONALITY"


def test_primary_uses_sorted_daily_net_excess() -> None:
    rows = [(f"2026-01-{i:02d}", "UP", .02, .01) for i in range(1, 16)] + [(f"2026-02-{i:02d}", "DOWN", -.01, -.01) for i in range(1, 16)]
    assert primary_assessment(list(reversed(rows)))["difference_of_mean_daily_excess"] == .01
