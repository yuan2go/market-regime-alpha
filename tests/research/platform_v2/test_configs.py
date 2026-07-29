from __future__ import annotations

import pytest

from market_regime_alpha.research.platform_v2.configs import (
    CapitalEvolutionModelConfig,
    CandidateDiscoveryModelConfig,
    MarketRegimeModelConfig,
    ResearchPipelineConfig,
    ThemeRotationModelConfig,
    default_research_pipeline_config,
)


def test_research_configs_are_versioned_and_content_addressed() -> None:
    first = default_research_pipeline_config()
    second = default_research_pipeline_config()

    assert first == second
    assert first.configuration_hash.startswith("sha256:")
    assert str(first.configuration_id).startswith("research-pipeline-config-")
    assert first.assumptions == (
        "MODEL_ASSUMPTION",
        "NOT_EMPIRICALLY_VALIDATED",
    )
    assert ResearchPipelineConfig.from_canonical_dict(
        first.to_canonical_dict()
    ) == first


@pytest.mark.parametrize(
    "config",
    (
        MarketRegimeModelConfig(),
        ThemeRotationModelConfig(),
        CapitalEvolutionModelConfig(),
        CandidateDiscoveryModelConfig(),
    ),
)
def test_each_model_config_round_trips(config: object) -> None:
    cls = type(config)
    payload = config.to_canonical_dict()  # type: ignore[attr-defined]
    assert cls.from_canonical_dict(payload) == config  # type: ignore[attr-defined]


def test_weight_changes_change_configuration_identity() -> None:
    baseline = ThemeRotationModelConfig()
    changed = ThemeRotationModelConfig(
        relative_strength_1d_weight=0.04,
        relative_strength_3d_weight=0.11,
    )
    assert baseline.configuration_hash != changed.configuration_hash
    assert baseline.configuration_id != changed.configuration_id


def test_invalid_model_weights_are_rejected() -> None:
    with pytest.raises(ValueError, match="sum to 1"):
        CandidateDiscoveryModelConfig(market_regime_weight=0.90)
