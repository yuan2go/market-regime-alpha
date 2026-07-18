from market_regime_alpha.research.mr2b_f2b_statistics import PrimaryObservationSet
from market_regime_alpha.research.mr2b_f2b_v2_statistics import assess_primary_coverage
from market_regime_alpha.research.mr2b_f2b_v2_protocol import frozen_f2b_v2_protocol


def test_low_up_slice_is_assessed_before_statistics() -> None:
    rows = PrimaryObservationSet((), total_date_count=44, flat_count=0, unavailable_count=0)
    coverage = assess_primary_coverage(rows, up_count=14, down_count=30, protocol=frozen_f2b_v2_protocol())
    assert coverage.sufficient_for_statistics is False
    assert coverage.insufficiency_reasons == ("INSUFFICIENT_UP_SLICE",)


def test_flat_and_unavailable_dates_remain_visible_in_coverage() -> None:
    rows = PrimaryObservationSet((), total_date_count=60, flat_count=26, unavailable_count=1)
    coverage = assess_primary_coverage(rows, up_count=14, down_count=19, protocol=frozen_f2b_v2_protocol())
    assert coverage.flat_count == 26
    assert coverage.unavailable_count == 1
    assert coverage.context_complete is False
    assert coverage.insufficiency_reasons == (
        "INSUFFICIENT_UP_SLICE",
        "CONTEXT_COVERAGE_INCOMPLETE",
    )
