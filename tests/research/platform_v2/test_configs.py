from __future__ import annotations

from dataclasses import replace

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


@pytest.mark.parametrize(
    "configuration",
    (
        MarketRegimeModelConfig(),
        ThemeRotationModelConfig(),
        CapitalEvolutionModelConfig(),
        CandidateDiscoveryModelConfig(),
    ),
)
def test_model_configuration_cannot_remove_unvalidated_assumption_ceiling(
    configuration: object,
) -> None:
    with pytest.raises(ValueError, match="assumptions are frozen"):
        replace(configuration, assumptions=("EMPIRICALLY_VALIDATED",))


def test_model_coverage_and_confidence_accept_unit_interval_boundaries() -> None:
    assert MarketRegimeModelConfig(minimum_coverage=0.0).minimum_coverage == 0.0
    assert (
        ThemeRotationModelConfig(minimum_confidence=1.0).minimum_confidence
        == 1.0
    )
    assert (
        CapitalEvolutionModelConfig(
            minimum_theme_confidence=0.0
        ).minimum_theme_confidence
        == 0.0
    )


def test_model_coverage_and_confidence_reject_outside_unit_interval() -> None:
    with pytest.raises(ValueError, match="within"):
        MarketRegimeModelConfig(minimum_coverage=1.01)
    with pytest.raises(ValueError, match="within"):
        ThemeRotationModelConfig(minimum_confidence=-0.01)
    with pytest.raises(ValueError, match="within"):
        CapitalEvolutionModelConfig(minimum_theme_confidence=1.01)
