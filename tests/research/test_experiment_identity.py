from __future__ import annotations

import pytest

from market_regime_alpha.core.identity import (
    DatasetId,
    FeatureDefinitionId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.research.experiment_identity import ExperimentIdentity


def _identity(*, semantic_refs: tuple[tuple[str, str], ...] = ()) -> ExperimentIdentity:
    return ExperimentIdentity(
        code_revision="abc123",
        dataset_id=DatasetId("dataset-001"),
        config_hash="config-hash-001",
        universe_id=UniverseId("universe-001"),
        target_id=TargetId("target-next-session-return-v1"),
        feature_definition_ids=(
            FeatureDefinitionId("feature-momentum-20d-v1"),
            FeatureDefinitionId("feature-liquidity-20d-v1"),
        ),
        semantic_refs=semantic_refs,
    )


def test_experiment_identity_hash_is_deterministic() -> None:
    first = _identity(semantic_refs=(("metric_contract", "candidate-ranking-v1"), ("run_mode", "RESEARCH")))
    second = _identity(semantic_refs=(("run_mode", "RESEARCH"), ("metric_contract", "candidate-ranking-v1")))

    assert first.to_canonical_json() == second.to_canonical_json()
    assert first.identity_hash == second.identity_hash
    assert str(first.experiment_id).startswith("exp-")


def test_result_affecting_change_changes_identity() -> None:
    baseline = _identity()
    changed = ExperimentIdentity(
        code_revision="abc123",
        dataset_id=DatasetId("dataset-002"),
        config_hash="config-hash-001",
        universe_id=UniverseId("universe-001"),
        target_id=TargetId("target-next-session-return-v1"),
        feature_definition_ids=baseline.feature_definition_ids,
    )

    assert baseline.identity_hash != changed.identity_hash
    assert baseline.experiment_id != changed.experiment_id


def test_duplicate_feature_identity_is_rejected() -> None:
    feature = FeatureDefinitionId("feature-momentum-20d-v1")
    with pytest.raises(ValueError, match="duplicate"):
        ExperimentIdentity(
            code_revision="abc123",
            dataset_id=DatasetId("dataset-001"),
            config_hash="config-hash-001",
            feature_definition_ids=(feature, feature),
        )


def test_duplicate_semantic_ref_keys_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate keys"):
        _identity(semantic_refs=(("metric_contract", "v1"), ("metric_contract", "v2")))
