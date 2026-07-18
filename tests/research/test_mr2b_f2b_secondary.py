import pytest

from market_regime_alpha.research.mr2b_f2b_secondary import benjamini_hochberg


def test_benjamini_hochberg_is_monotone_bounded_and_restores_order() -> None:
    values = (0.04, 0.001, 0.02, 0.5)
    adjusted = benjamini_hochberg(values)
    assert adjusted == pytest.approx((0.053333333333, 0.004, 0.04, 0.5))
    assert all(0.0 <= value <= 1.0 for value in adjusted)
