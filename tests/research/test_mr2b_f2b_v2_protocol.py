from dataclasses import replace

import pytest

from market_regime_alpha.research.mr2b_f2b_v2_protocol import frozen_f2b_v2_protocol


def test_v2_protocol_freezes_all_statistical_parameters() -> None:
    protocol = frozen_f2b_v2_protocol()
    assert protocol.bootstrap_sensitivity_block_lengths == (3, 10)
    assert protocol.minimum_valid_bootstrap_draw_ratio == 0.95
    assert protocol.half_minimum_slice_size == 5
    assert protocol.rolling_window == 20
    assert protocol.required_positive_panel_count == 4
    assert protocol.secondary_bootstrap_draws == 2_000


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("bootstrap_interval", 0.90),
        ("minimum_valid_bootstrap_draw_ratio", 0.90),
        ("half_minimum_slice_size", 6),
        ("rolling_window", 15),
        ("largest_contribution_limit", 0.40),
        ("secondary_bootstrap_draws", 1_000),
    ),
)
def test_every_execution_parameter_changes_protocol_identity(field: str, value: object) -> None:
    protocol = frozen_f2b_v2_protocol()
    assert replace(protocol, **{field: value}).protocol_id != protocol.protocol_id
