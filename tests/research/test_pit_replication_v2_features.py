from dataclasses import replace

import pytest

from market_regime_alpha.research.pit_replication_success_v2_features import reconstruct_b1e_scores
from market_regime_alpha.research.pit_replication_success_v2_protocol import (
    frozen_pit_replication_success_v2_protocol,
)
from tests.research.pit_replication_v2_fixtures import build_test_success_inputs


def test_b1e_rankings_are_reconstructed_from_feature_evidence() -> None:
    inputs = build_test_success_inputs()
    scores, rankings = reconstruct_b1e_scores(
        inputs.feature_rows, protocol=frozen_pit_replication_success_v2_protocol(test_only=True)
    )
    assert len(scores) == 10
    assert sorted(row["rank"] for row in rankings if row["decision_date"] == "2026-01-05") == [1, 2, 3, 4, 5]


def test_late_feature_evidence_fails_closed() -> None:
    inputs = build_test_success_inputs()
    row = {**inputs.feature_rows[0], "feature_available_at": "2026-01-05T15:00:00+08:00"}
    with pytest.raises(ValueError, match="Decision Time"):
        reconstruct_b1e_scores(
            (row, *inputs.feature_rows[1:]),
            protocol=frozen_pit_replication_success_v2_protocol(test_only=True),
        )


def test_changed_model_spec_hash_is_rejected() -> None:
    protocol = frozen_pit_replication_success_v2_protocol(test_only=True)
    with pytest.raises(ValueError, match="model specification"):
        replace(protocol, ranking_model_spec_hash="forged")
