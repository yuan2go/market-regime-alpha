from __future__ import annotations

from dataclasses import dataclass

import pytest

from market_regime_alpha.legacy.macd_experiment_adapter import adapt_legacy_macd_experiment_identity


@dataclass(frozen=True)
class FakeLegacyMACDIdentity:
    git_commit: str = "abc123"
    dataset_version: str = "legacy-dataset-v7"
    data_split_hash: str = "split-hash"
    pipeline_id: str = "macd-pipeline-v1"
    execution_config_hash: str = "execution-hash"
    sizing_owner: str = "legacy-strategy"


def test_legacy_macd_adapter_preserves_identity_anchors_without_inventing_scope() -> None:
    adapted = adapt_legacy_macd_experiment_identity(
        FakeLegacyMACDIdentity(),
        legacy_config_hash="legacy-config-hash",
    )

    assert adapted.code_revision == "abc123"
    assert str(adapted.dataset_id) == "legacy-macd-dataset-version:legacy-dataset-v7"
    assert adapted.target_id is None
    assert adapted.universe_id is None
    assert adapted.execution_assumption_ref == "legacy-macd-execution:execution-hash"
    assert dict(adapted.semantic_refs)["legacy_data_split_hash"] == "split-hash"


def test_legacy_macd_adapter_rejects_missing_required_shape() -> None:
    with pytest.raises(TypeError):
        adapt_legacy_macd_experiment_identity(object(), legacy_config_hash="hash")  # type: ignore[arg-type]
