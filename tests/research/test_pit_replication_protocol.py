from dataclasses import replace

import pytest

from market_regime_alpha.research.pit_replication_protocol import (
    CandidateFeatureExperiment,
    frozen_pit_replication_protocol,
)


def test_protocol_freezes_b1e_without_context_or_winner_selection() -> None:
    protocol = frozen_pit_replication_protocol()
    assert protocol.candidate_model_id == "prr-mvp-1-b1-e-v1"
    assert protocol.top_k == 5
    assert protocol.context_id is None
    assert protocol.feature_tuning_policy == "FORBIDDEN_ON_VALIDATION_PARTITION"
    assert protocol.model_winner_selection == "FORBIDDEN"
    assert protocol.development_partition_id != protocol.validation_partition_id


def test_partition_id_overlap_fails_closed() -> None:
    protocol = frozen_pit_replication_protocol()
    with pytest.raises(ValueError, match="partition"):
        replace(protocol, validation_partition_id=protocol.development_partition_id)


def test_feature_ablation_contract_cannot_use_validation_for_tuning() -> None:
    with pytest.raises(ValueError, match="validation"):
        CandidateFeatureExperiment(
            experiment_id="ablation",
            base_model_id="prr-mvp-1-b1-e-v1",
            added_feature_ids=("feature-x",),
            removed_feature_ids=(),
            development_partition_id="development",
            validation_partition_id="validation",
            status="TUNING_ON_VALIDATION",
        )
