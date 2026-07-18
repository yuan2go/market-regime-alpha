from market_regime_alpha.research.pit_replication_success_v2 import (
    build_pit_replication_success_results,
)
from market_regime_alpha.research.pit_replication_success_v2_protocol import (
    frozen_pit_replication_success_v2_protocol,
)
from tests.research.pit_replication_v2_fixtures import build_test_success_inputs


def test_matched_k_covers_every_date_and_all_256_seeds() -> None:
    results = build_pit_replication_success_results(
        build_test_success_inputs(), protocol=frozen_pit_replication_success_v2_protocol(test_only=True)
    )
    assert len(results.selection_rows) == 2 * 256 * 5
    assert len(results.matched_k_return_rows) == 2 * 256 * 3
    assert results.path_status == "PATH_DIAGNOSTICS_UNAVAILABLE"
    assert dict(results.assessment.cost_robustness_effects).keys() == {"LOW", "BASE", "HIGH"}
    assert results.assessment.rolling_window_count == 1
    assert results.assessment.leave_one_out_minimum is not None
