from dataclasses import replace

import pytest

from market_regime_alpha.research.pit_replication_success_v2_protocol import (
    frozen_pit_replication_success_v2_protocol,
)


def test_ranking_target_and_1030_evaluation_endpoint_are_distinct() -> None:
    protocol = frozen_pit_replication_success_v2_protocol()
    assert protocol.ranking_dataset_target_id != protocol.primary_evaluation_mark_id
    assert protocol.primary_evaluation_time == "10:30"
    with pytest.raises(ValueError, match="separate"):
        replace(protocol, primary_evaluation_mark_id=protocol.ranking_dataset_target_id)


def test_cost_model_change_changes_protocol_identity() -> None:
    protocol = frozen_pit_replication_success_v2_protocol()
    changed = replace(protocol, cost_model_id="changed-cost-model")
    assert changed.protocol_id != protocol.protocol_id


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("bootstrap_seed", 9),
        ("rolling_window", 21),
        ("largest_contribution_limit", 0.49),
        ("top_3_contribution_limit", 0.74),
        ("required_positive_seed_panels", 3),
    ),
)
def test_statistical_governance_changes_protocol_identity(field: str, value: object) -> None:
    protocol = frozen_pit_replication_success_v2_protocol()
    if field == "required_positive_seed_panels":
        with pytest.raises(ValueError, match="four seed panels"):
            replace(protocol, **{field: value})
        return
    changed = replace(protocol, **{field: value})
    assert changed.protocol_id != protocol.protocol_id
